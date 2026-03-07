# Strategy & Indicator Development Guide

## Overview

This document defines the strict architecture rules for extending the trading system with new indicators or strategies.

**AI ASSISTANT INSTRUCTION**: If asked to add a new strategy or technical indicator, YOU MUST follow these rules exactly to ensure system performance and modularity. Do not calculate indicators inside strategy classes.

---

## 🏗️ Architecture Rule: Centralized Indicators

To optimize performance, the system is designed so that technical indicators are calculated exactly **ONCE** per DataFrame, rather than re-calculating them inside every individual strategy.

We use the `pandas-ta` library centrally inside `core/indicator_engine.py`.

### How to Add a New Indicator

If a new strategy requires an indicator that isn't already being calculated (e.g., Average True Range - ATR, or Bollinger Bands), follow these steps:

1. **Open `trading_on_tcbs_api/stock_system_v2/core/indicator_engine.py`**.
2. **Update the Default Config**: In the `get_default_config()` method, add the new indicator name to the dictionary so the engine knows to process it.
   ```python
   def get_default_config(self) -> Dict[str, Any]:
       return {
           "sma": [20, 50],
           "rsi": [14],
           "atr": [14]  # <-- ADDED NEW INDICATOR
       }
   ```
3. **Map the `pandas-ta` Execution**: In the `append_indicators(self, df)` method, add a block that iterates over your new config and appends the indicator to the DataFrame using the `df.ta` extension from `pandas-ta`.
   ```python
   # ATR
   if "atr" in self.config:
       for length in self.config["atr"]:
           data.ta.atr(length=length, append=True)
   ```
4. **Column Naming Convention**: `pandas-ta` auto-generates column names. At the end of `append_indicators`, all columns are standardized to **lowercase**. Therefore, `ATR_14` will become `atr_14`. Your strategies must look for the lowercase version.

---

## 🧠 Building a New Strategy

All strategies must be highly modular, relying entirely on the pre-calculated columns from the `IndicatorEngine`. They should never do complex Pandas rolling maths internally.

### Steps to Implement:

1. **Create the File**: Create `trading_on_tcbs_api/stock_system_v2/strategies/my_new_strategy.py`.
2. **Inherit**: Inherit from `SignalStrategy`.
3. **Implement `generate_signals`**:
   - `df = data.copy()`
   - Identify the pre-calculated column you need (e.g., `atr_14`).
   - Throw a `ValueError` if the column is missing (catches config mistakes early).
   - Initialize `df['signal'] = 0`.
   - Apply boolean masking to set BUY (`1`) and SELL (`-1`) signals.

**Example Template:**
```python
import pandas as pd
from .strategy import SignalStrategy

class MyNewStrategy(SignalStrategy):
    def __init__(self, period: int = 14):
        self.period = period
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 1. Look for pre-calculated indicator column
        atr_col = f'atr_{self.period}'
        if atr_col not in df.columns:
            raise ValueError(f"Missing required indicator column from IndicatorEngine: {atr_col}")
            
        df['signal'] = 0
        
        # 2. Buy/Sell Logic (Example pseudo-logic)
        df.loc[df['close'] > df[atr_col], 'signal'] = 1   # BUY
        df.loc[df['close'] < target_buy_price, 'signal'] = -1  # SELL
        
        # 3. Handle signal inversion!
        if getattr(self, 'invert', False):
            df['signal'] = df['signal'] * -1
            
        return df
```

### Advanced Tricks: Reusing Strategies
Before creating a new strategy, see if existing ones can be combined or manipulated:
-   **Price vs Indicator**: If you want "Price vs SMA(20)", you don't need a new strategy. Just use `SimpleMAStrategy(short_window=1, long_window=20)`, as the engine maps `window=1` directly to the `close` price.
-   **Inverted Signals (Sell on Rip / Mean Reversion)**: If a standard trend-following strategy generates a BUY, but you want to fade it, pass `invert=True` to the strategy initialization to instantly turn all `1`s into `-1`s and vice versa.

---

## ⚙️ Registering the Strategy

Once your strategy class is built, ensure it is exposed cleanly in `trading_on_tcbs_api/stock_system_v2/strategies/__init__.py`.

Then, inject it into the `CombinedStrategy` router in your scripts.

**Locations to update:**
1.  `trading_on_tcbs_api/stock_system_v2/scripts/scan_market.py`
2.  `trading_on_tcbs_api/stock_system_v2/scripts/verify_backtest.py`
3.  `trading_on_tcbs_api/stock_system_v2/core/auto_trader.py`

**Example:**
```python
from trading_on_tcbs_api.stock_system_v2.strategies import CombinedStrategy, MyNewStrategy

# Initialize
my_strat = MyNewStrategy(period=14, invert=True)

# Add to router
strategy = CombinedStrategy(
    strategies=[],
    buy_strategies=[my_strat], # Only check for BUYS
    sell_strategies=[...],
    buy_mode="AND",
    sell_mode="OR"
)
```

By following this exact pattern, the system remains lightning fast, incredibly modular, and eliminates redundant mathematics when scanning large markets (like the VN30 list).
