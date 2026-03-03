# Stock Trading System - Technical Glossary

## Core Classes and Components

### **BaseIndicator** (`indicators/base.py`)
Abstract base class for all technical indicators.

**Key Methods:**
- `calculate(data: np.ndarray, **kwargs) -> IndicatorResult`: Main calculation method
- `generate_signals(values, current_price, **kwargs) -> List[Signal]`: Generate buy/sell signals
- `validate_data(data) -> bool`: Validate input data quality
- `get_required_periods() -> int`: Minimum data points needed

**Usage:**
```python
class CustomIndicator(BaseIndicator):
    def calculate(self, data, **kwargs):
        # Implementation here
        return IndicatorResult(values, signals, metadata)
```

---

### **IndicatorResult** (`indicators/base.py`)
Container for indicator calculation results.

**Attributes:**
- `values: Union[np.ndarray, Dict[str, np.ndarray]]`: Calculated indicator values
- `signals: List[Signal]`: Generated trading signals
- `metadata: Dict[str, Any]`: Additional information (timestamps, parameters)

---

### **Signal** (`indicators/base.py`)
Represents a trading signal with strength and metadata.

**Attributes:**
- `signal_type: SignalType`: BUY, SELL, or HOLD
- `strength: float`: Signal confidence (0.0 to 1.0)
- `timestamp: datetime`: When signal was generated
- `price: float`: Price at signal generation
- `indicator_name: str`: Source indicator
- `metadata: Dict[str, Any]`: Additional signal data

---

### **SignalType** (`indicators/base.py`)
Enumeration for signal types.

**Values:**
- `BUY`: Long position signal
- `SELL`: Short position signal  
- `HOLD`: No action signal

---

### **IndicatorRegistry** (`indicators/base.py`)
Registry for managing available indicators.

**Methods:**
- `register_indicator(name: str, indicator_class: Type[BaseIndicator])`: Register new indicator
- `create_indicator(name: str, **kwargs) -> BaseIndicator`: Create indicator instance
- `list_indicators() -> List[str]`: List all registered indicators
- `get_indicator_info(name: str) -> Dict`: Get indicator metadata

---

## Technical Indicators

### **RSI** (`indicators/talib_indicators.py`)
Relative Strength Index - momentum oscillator measuring speed and change of price movements.

**Parameters:**
- `period: int = 14`: Calculation period
- `oversold: float = 30`: Oversold threshold
- `overbought: float = 70`: Overbought threshold

**Signals:**
- BUY when RSI < oversold threshold
- SELL when RSI > overbought threshold

---

### **SMA** (`indicators/talib_indicators.py`)
Simple Moving Average - arithmetic mean of prices over specified period.

**Parameters:**
- `period: int = 20`: Moving average period

**Signals:**
- BUY when price > SMA (uptrend)
- SELL when price < SMA (downtrend)

---

### **EMA** (`indicators/talib_indicators.py`)
Exponential Moving Average - weighted average giving more importance to recent prices.

**Parameters:**
- `period: int = 20`: Moving average period
- `alpha: float = None`: Smoothing factor (auto-calculated if None)

**Signals:**
- BUY when price > EMA (uptrend)
- SELL when price < EMA (downtrend)

---

### **MACD** (`indicators/talib_indicators.py`)
Moving Average Convergence Divergence - trend-following momentum indicator.

**Parameters:**
- `fast_period: int = 12`: Fast EMA period
- `slow_period: int = 26`: Slow EMA period
- `signal_period: int = 9`: Signal line EMA period

**Returns:**
- `macd`: MACD line (fast EMA - slow EMA)
- `signal`: Signal line (EMA of MACD)
- `histogram`: MACD histogram (MACD - signal)

**Signals:**
- BUY when MACD crosses above signal line
- SELL when MACD crosses below signal line

---

### **BollingerBands** (`indicators/talib_indicators.py`)
Bollinger Bands - volatility indicator with upper and lower bands.

**Parameters:**
- `period: int = 20`: Moving average period
- `std_dev: float = 2.0`: Standard deviation multiplier

**Returns:**
- `upper`: Upper band (SMA + std_dev * std)
- `middle`: Middle band (SMA)
- `lower`: Lower band (SMA - std_dev * std)

**Signals:**
- BUY when price touches lower band (oversold)
- SELL when price touches upper band (overbought)

---

### **CustomRSI** (`indicators/custom_indicators.py`)
Pure Python implementation of RSI (fallback when TA-Lib unavailable).

**Parameters:**
- `period: int = 14`: RSI calculation period
- `oversold: float = 30`: Oversold threshold
- `overbought: float = 70`: Overbought threshold

---

### **PriceMomentum** (`indicators/custom_indicators.py`)
Rate of price change indicator.

**Parameters:**
- `period: int = 10`: Lookback period
- `threshold: float = 0.02`: Minimum change threshold for signals

**Calculation:**
```python
momentum = (current_price - price_n_periods_ago) / price_n_periods_ago
```

---

### **Volatility** (`indicators/custom_indicators.py`)
Price volatility measurement using standard deviation.

**Parameters:**
- `period: int = 20`: Calculation period
- `threshold: float = 0.05`: High volatility threshold

---

## Signal Generation System

### **SignalGenerator** (`indicators/signal_generator.py`)
Main class for combining multiple indicators and generating trading signals.

**Methods:**
- `add_indicator(name: str, indicator: BaseIndicator)`: Add indicator
- `add_rule(rule: SignalRule)`: Add combination rule
- `generate_signals(data: Dict[str, np.ndarray], current_price: float) -> List[Signal]`: Generate combined signals
- `get_indicator_results() -> Dict[str, IndicatorResult]`: Get individual indicator results

---

### **SignalRule** (`indicators/signal_generator.py`)
Defines how to combine signals from multiple indicators.

**Attributes:**
- `name: str`: Rule identifier
- `indicators: List[str]`: Indicators to combine
- `conditions: Dict[str, Dict]`: Conditions for each indicator
- `logic: CombinationLogic`: How to combine signals
- `weights: Optional[Dict[str, float]]`: Weights for WEIGHTED logic
- `min_strength: float`: Minimum combined signal strength

**Example:**
```python
rule = SignalRule(
    name="RSI_SMA_BUY",
    indicators=["RSI", "SMA"],
    conditions={
        "RSI": {"signal_type": [SignalType.BUY], "min_strength": 0.3},
        "SMA": {"signal_type": [SignalType.BUY], "min_strength": 0.2}
    },
    logic=CombinationLogic.AND,
    min_strength=0.4
)
```

---

### **CombinationLogic** (`indicators/signal_generator.py`)
Enumeration for signal combination methods.

**Values:**
- `AND`: All indicators must agree
- `OR`: Any indicator can trigger
- `WEIGHTED`: Weighted average of signal strengths
- `MAJORITY`: Majority of indicators must agree

---

### **CommonSignalRules** (`indicators/signal_generator.py`)
Pre-built signal rule patterns.

**Methods:**
- `rsi_oversold_overbought() -> SignalRule`: Classic RSI reversal signals
- `rsi_ma_combo() -> SignalRule`: RSI with moving average confirmation
- `macd_crossover() -> SignalRule`: MACD crossover signals
- `bollinger_breakout() -> SignalRule`: Bollinger band breakout signals

---

## Trading Strategy Classes

### **TradingConfig** (`core/stock_trading_strategy.py`)
Configuration dataclass for trading strategy parameters.

**Attributes:**
- `symbols: List[str]`: Stocks to trade
- `max_position_per_symbol: int`: Maximum shares per stock
- `max_portfolio_value: float`: Portfolio value limit
- `risk_per_trade: float`: Risk percentage per trade (0.0-1.0)
- `stop_loss_pct: float`: Stop loss percentage
- `take_profit_pct: float`: Take profit percentage
- `min_signal_strength: float`: Minimum signal strength threshold
- `trading_hours: Tuple[Tuple[int, int], Tuple[int, int]]`: Market hours
- `data_update_interval: int`: Data refresh interval (seconds)
- `use_talib: bool`: Whether to use TA-Lib indicators

---

### **StockTradingStrategy** (`core/stock_trading_strategy.py`)
Main trading strategy orchestrator.

**Key Methods:**
- `initialize(account_no: str)`: Initialize strategy with API client
- `start_trading()`: Start the trading loop
- `stop_trading()`: Stop trading gracefully
- `process_signals(symbol: str, signals: List[Signal])`: Process signals for a symbol
- `calculate_position_size(symbol: str, price: float, stop_loss_pct: float) -> int`: Calculate position size
- `manage_existing_positions()`: Monitor and manage open positions
- `get_strategy_status() -> Dict[str, Any]`: Get current strategy status

---

## Data Management Classes

### **HistoricalDataManager** (`data/historical_data_manager.py`)
Manages historical price data with caching and persistence.

**Methods:**
- `get_historical_data(symbol: str, days: int) -> np.ndarray`: Get historical prices
- `save_historical_data(symbol: str, data: np.ndarray)`: Save data to cache
- `update_cache(symbol: str, new_data: np.ndarray)`: Update cached data
- `validate_data_quality(data: np.ndarray) -> bool`: Validate data integrity
- `get_data_for_indicators(symbol: str, lookback: int) -> np.ndarray`: Get data for indicator calculation

---

### **RealTimeDataIntegrator** (`data/historical_data_manager.py`)
Integrates real-time prices with historical data.

**Methods:**
- `update_with_realtime(symbol: str, current_price: float) -> np.ndarray`: Update data with current price
- `merge_historical_realtime(historical: np.ndarray, realtime: float) -> np.ndarray`: Merge datasets
- `get_combined_data(symbol: str, current_price: float) -> np.ndarray`: Get combined historical + real-time data

---

## API Integration Classes

### **StockTradingClient** (`core/stock_api_client.py`)
Extended TCBS API client for stock trading operations.

**Order Management:**
- `place_stock_order(symbol: str, side: str, quantity: int, price: float) -> str`: Place order
- `modify_stock_order(order_id: str, quantity: int, price: float) -> bool`: Modify order
- `cancel_stock_order(order_id: str) -> bool`: Cancel order
- `get_stock_orders(symbol: str = None) -> List[Dict]`: Get order history

**Position Management:**
- `get_stock_positions() -> List[Dict]`: Get all positions
- `get_position_by_symbol(symbol: str) -> Optional[Dict]`: Get position for symbol

**Portfolio Information:**
- `get_cash_balance() -> float`: Get available cash
- `get_buying_power() -> float`: Get buying power
- `get_portfolio_summary() -> Dict[str, Any]`: Get portfolio overview

**Market Data:**
- `get_stock_price(symbol: str) -> float`: Get current price
- `get_stock_info(symbol: str) -> Dict[str, Any]`: Get stock information

---

## Utility Classes

### **PositionManager** (`utils/position_manager.py`)
Manages trading positions and portfolio state.

**Methods:**
- `add_position(symbol: str, quantity: int, entry_price: float)`: Add new position
- `update_position(symbol: str, quantity: int, price: float)`: Update existing position
- `close_position(symbol: str)`: Close position
- `get_position(symbol: str) -> Optional[Dict]`: Get position details
- `get_portfolio_value() -> float`: Calculate total portfolio value
- `get_unrealized_pnl() -> float`: Calculate unrealized P&L

---

### **FastLogger** (`logger_utils/fast_logger.py`)
High-performance async logging system.

**Methods:**
- `log(message: str, level: str = "INFO")`: Log message
- `log_error(message: str, exception: Exception = None)`: Log error
- `log_trade(symbol: str, action: str, details: Dict)`: Log trading action
- `flush()`: Flush pending log entries

---

## Configuration and Constants

### **Market Hours**
Vietnamese stock market trading sessions:
- **Morning Session**: 09:00 - 11:30
- **Afternoon Session**: 13:00 - 15:00

### **Signal Strength Scale**
- **0.0 - 0.3**: Weak signal
- **0.3 - 0.6**: Moderate signal  
- **0.6 - 0.8**: Strong signal
- **0.8 - 1.0**: Very strong signal

### **Risk Management Parameters**
- **Default Risk per Trade**: 2% of portfolio
- **Default Stop Loss**: 5% from entry
- **Default Take Profit**: 10% from entry
- **Maximum Position**: 100,000 shares per symbol
- **Portfolio Limit**: 5,000,000,000 VND

### **Data Validation Rules**
- **Minimum Data Points**: 50 for most indicators
- **Price Range**: 1,000 - 1,000,000 VND per share
- **Volume Range**: > 0 shares
- **Date Range**: Within last 5 years

## Error Handling

### **Common Exceptions**
- `InsufficientDataError`: Not enough historical data
- `InvalidSignalError`: Invalid signal parameters
- `APIConnectionError`: TCBS API connection issues
- `OrderExecutionError`: Order placement failures
- `RiskLimitExceededError`: Risk management violations

### **Error Recovery Strategies**
- **Data Errors**: Use cached data or skip calculation
- **API Errors**: Retry with exponential backoff
- **Signal Errors**: Log and continue with other signals
- **Order Errors**: Cancel and retry or skip trade

This glossary provides comprehensive documentation of all classes, methods, and concepts used in the stock trading system.
