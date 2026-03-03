# Stock Trading System - Architecture & Structure

## System Overview

The Stock Trading System is a comprehensive technical analysis-based trading platform for Vietnamese stock markets. Built on top of the VN30 futures trading infrastructure, it provides automated stock trading using multiple technical indicators, signal generation, and risk management.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Stock Trading System                             │
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────┐  │
│  │  Configuration  │    │   Data Manager  │    │    Strategy Engine      │  │
│  │ - Trading Config│    │  - Historical   │    │  - Signal Generation    │  │
│  │ - Indicators    │    │  - Real-time    │    │  - Risk Management      │  │
│  │ - Signal Rules  │    │  - Caching      │    │  - Order Execution      │  │
│  └─────────────────┘    └─────────────────┘    └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼──────────┐    ┌───────────▼──────────┐    ┌───────────▼──────────┐
│ Indicator Engine │    │   Signal Generator   │    │   Trading Strategy   │
│                  │    │                      │    │                      │
│ ┌──────────────┐ │    │ ┌──────────────────┐ │    │ ┌──────────────────┐ │
│ │ TA-Lib       │ │    │ │ Combination      │ │    │ │ Multi-Symbol     │ │
│ │ - RSI        │ │    │ │ Logic            │ │    │ │ Trading          │ │
│ │ - SMA/EMA    │ │    │ │ - AND/OR/WEIGHTED│ │    │ │ - Position Mgmt  │ │
│ │ - MACD       │ │    │ │ - Signal Rules   │ │    │ │ - Risk Controls  │ │
│ │ - Bollinger  │ │    │ │ - Strength Filter│ │    │ │ - Stop Loss/TP   │ │
│ └──────────────┘ │    │ └──────────────────┘ │    │ └──────────────────┘ │
│                  │    │                      │    │                      │
│ ┌──────────────┐ │    │ ┌──────────────────┐ │    │ ┌──────────────────┐ │
│ │ Custom       │ │    │ │ Pre-built Rules  │ │    │ │ Portfolio Mgmt   │ │
│ │ - Custom RSI │ │    │ │ - RSI Oversold   │ │    │ │ - Cash Balance   │ │
│ │ - Custom MA  │ │    │ │ - MA Crossover   │ │    │ │ - Buying Power   │ │
│ │ - Momentum   │ │    │ │ - MACD Signal    │ │    │ │ - P&L Tracking   │ │
│ │ - Volatility │ │    │ │ - Combined Rules │ │    │ │ - Performance    │ │
│ └──────────────┘ │    │ └──────────────────┘ │    │ └──────────────────┘ │
└──────────────────┘    └──────────────────────┘    └──────────────────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
        ┌───────────────────────────▼───────────────────────────┐
        │                 Data Layer                            │
        │                                                       │
        │ ┌─────────────────┐  ┌─────────────────┐  ┌─────────┐ │
        │ │ Historical Data │  │ Real-time Data  │  │ API     │ │
        │ │ Manager         │  │ Integrator      │  │ Client  │ │
        │ │ - File Caching  │  │ - Price Updates │  │ - TCBS  │ │
        │ │ - Data Validation│  │ - Stream Merge  │  │ - Orders│ │
        │ │ - Async I/O     │  │ - Indicator Sync│  │ - Data  │ │
        │ └─────────────────┘  └─────────────────┘  └─────────┘ │
        └───────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────▼───────────────────────────┐
        │                 TCBS OpenAPI                          │
        │ - Stock Trading Endpoints                             │
        │ - Market Data Streaming                               │
        │ - Order Management                                    │
        │ - Portfolio Information                               │
        └───────────────────────────────────────────────────────┘
```

## Core Components

### 1. **Indicator Engine** (`indicators/`)

The indicator engine provides technical analysis capabilities with dual implementation strategy:

#### TA-Lib Integration (`talib_indicators.py`)
- **RSI**: Relative Strength Index with overbought/oversold signals
- **SMA/EMA**: Simple and Exponential Moving Averages with trend signals
- **MACD**: Moving Average Convergence Divergence with crossover signals
- **Bollinger Bands**: Price volatility bands with breakout signals
- **Stochastic**: Momentum oscillator with overbought/oversold signals

#### Custom Implementations (`custom_indicators.py`)
- **CustomRSI**: Pure Python RSI implementation (fallback)
- **CustomSMA/EMA**: Moving averages without TA-Lib dependency
- **PriceMomentum**: Rate of price change indicator
- **Volatility**: Price volatility measurement

#### Base Framework (`base.py`)
```python
class BaseIndicator:
    - calculate(data) -> IndicatorResult
    - generate_signals(values, current_price) -> List[Signal]
    - validate_data(data) -> bool

class IndicatorRegistry:
    - register_indicator(name, indicator_class)
    - create_indicator(name, **kwargs) -> BaseIndicator
    - list_indicators() -> List[str]
```

### 2. **Signal Generation System** (`indicators/signal_generator.py`)

Advanced signal combination and filtering system:

#### Signal Combination Logic
- **AND**: All indicators must agree
- **OR**: Any indicator can trigger
- **WEIGHTED**: Weighted average of signal strengths
- **MAJORITY**: Majority of indicators must agree

#### Signal Rules Framework
```python
class SignalRule:
    - name: str
    - indicators: List[str]
    - conditions: Dict[str, Any]
    - logic: CombinationLogic
    - weights: Optional[Dict[str, float]]
    - min_strength: float

class SignalGenerator:
    - add_indicator(name, indicator)
    - add_rule(rule)
    - generate_signals(data, current_price) -> List[Signal]
```

#### Pre-built Signal Patterns
- **RSI Oversold/Overbought**: Classic RSI reversal signals
- **RSI + MA Combo**: RSI confirmation with moving average trend
- **MACD Crossover**: MACD line crossing signal line
- **Bollinger Breakout**: Price breaking Bollinger bands

### 3. **Trading Strategy Engine** (`core/stock_trading_strategy.py`)

Multi-symbol trading orchestration with comprehensive risk management:

#### Strategy Configuration
```python
@dataclass
class TradingConfig:
    symbols: List[str]                    # Stocks to trade
    max_position_per_symbol: int          # Max shares per stock
    max_portfolio_value: float            # Portfolio limit
    risk_per_trade: float                 # Risk percentage per trade
    stop_loss_pct: float                  # Stop loss percentage
    take_profit_pct: float                # Take profit percentage
    min_signal_strength: float            # Minimum signal threshold
    trading_hours: Tuple[Tuple[int, int], Tuple[int, int]]  # Market hours
    data_update_interval: int             # Data refresh interval
```

#### Core Strategy Methods
```python
class StockTradingStrategy:
    - initialize(account_no) -> None
    - start_trading() -> None
    - stop_trading() -> None
    - process_signals(symbol, signals) -> None
    - calculate_position_size(symbol, price, stop_loss_pct) -> int
    - manage_existing_positions() -> None
    - get_strategy_status() -> Dict[str, Any]
```

### 4. **Data Management Layer** (`data/`)

Efficient data handling with caching and real-time integration:

#### Historical Data Manager (`historical_data_manager.py`)
```python
class HistoricalDataManager:
    - get_historical_data(symbol, days) -> np.ndarray
    - save_historical_data(symbol, data) -> None
    - update_cache(symbol, new_data) -> None
    - validate_data_quality(data) -> bool
    - get_data_for_indicators(symbol, lookback) -> np.ndarray
```

#### Real-time Data Integration
```python
class RealTimeDataIntegrator:
    - update_with_realtime(symbol, current_price) -> np.ndarray
    - merge_historical_realtime(historical, realtime) -> np.ndarray
    - get_combined_data(symbol, current_price) -> np.ndarray
```

### 5. **API Integration Layer** (`core/stock_api_client.py`)

Extended TCBS API client for stock trading operations:

#### Stock Trading Operations
```python
class StockTradingClient(TCBSClient):
    # Order Management
    - place_stock_order(symbol, side, quantity, price) -> str
    - modify_stock_order(order_id, quantity, price) -> bool
    - cancel_stock_order(order_id) -> bool
    - get_stock_orders(symbol=None) -> List[Dict]
    
    # Position Management
    - get_stock_positions() -> List[Dict]
    - get_position_by_symbol(symbol) -> Optional[Dict]
    
    # Portfolio Information
    - get_cash_balance() -> float
    - get_buying_power() -> float
    - get_portfolio_summary() -> Dict[str, Any]
    
    # Market Data
    - get_stock_price(symbol) -> float
    - get_stock_info(symbol) -> Dict[str, Any]
```

## Data Flow Architecture

### 1. **Initialization Flow**
```
Config Load → Strategy Init → API Auth → Data Cache → Indicator Setup
```

### 2. **Trading Loop Flow**
```
Market Data → Historical Merge → Indicator Calc → Signal Gen → Risk Check → Order Place
     ↓              ↓               ↓             ↓           ↓           ↓
  Real-time    Cache Update    Technical Analysis  Rules   Position Size  Execution
```

### 3. **Signal Processing Pipeline**
```
Price Data → Individual Indicators → Signal Combination → Strength Filter → Trading Decision
    ↓              ↓                      ↓                    ↓               ↓
Raw OHLCV    RSI/MA/MACD/etc        AND/OR/WEIGHTED      Min Threshold    BUY/SELL/HOLD
```

## Risk Management Framework

### Position Sizing Algorithm
```python
def calculate_position_size(portfolio_value, risk_per_trade, entry_price, stop_loss_price):
    risk_amount = portfolio_value * risk_per_trade
    risk_per_share = abs(entry_price - stop_loss_price)
    position_size = min(risk_amount / risk_per_share, max_position_per_symbol)
    return int(position_size)
```

### Risk Controls
1. **Portfolio Level**: Maximum portfolio value limit
2. **Position Level**: Maximum shares per symbol
3. **Trade Level**: Risk percentage per trade
4. **Time Level**: Trading hours validation
5. **Signal Level**: Minimum signal strength threshold

## Configuration Management

### Trading Configuration (`config/stock_trading_config.json`)
```json
{
  "symbols": ["VIC", "VHM", "VNM", "SAB", "MSN"],
  "max_position_per_symbol": 100000,
  "max_portfolio_value": 5000000000,
  "risk_per_trade": 0.02,
  "stop_loss_pct": 0.05,
  "take_profit_pct": 0.10,
  "min_signal_strength": 0.4,
  "trading_hours": [[9, 0], [15, 0]],
  "data_update_interval": 60,
  "indicators": {
    "rsi": {"period": 14, "oversold": 30, "overbought": 70},
    "sma": {"period": 20},
    "ema": {"period": 20},
    "macd": {"fast_period": 12, "slow_period": 26, "signal_period": 9}
  },
  "signal_rules": {
    "rsi_oversold_overbought": {"enabled": true, "min_strength": 0.3},
    "rsi_ma_combo": {"enabled": true, "min_strength": 0.4},
    "macd_crossover": {"enabled": true, "min_strength": 0.3}
  }
}
```

## Logging and Monitoring

### Structured Logging (`logger_utils/fast_logger.py`)
- **Strategy Decisions**: Signal generation and trading logic
- **Order Execution**: Order placement, modification, cancellation
- **Risk Management**: Position sizing and risk control actions
- **Data Operations**: Cache updates and API calls
- **Error Handling**: Exception tracking and recovery

### Performance Metrics
- **Portfolio Performance**: P&L, returns, Sharpe ratio
- **Signal Quality**: Hit rate, false positive rate
- **Execution Quality**: Slippage, fill rates
- **System Performance**: Latency, throughput

## Scalability and Extensibility

### Horizontal Scaling
- **Multi-Symbol**: Parallel processing of different stocks
- **Multi-Strategy**: Multiple strategies running simultaneously
- **Multi-Timeframe**: Different timeframes for same symbols

### Vertical Scaling
- **Indicator Library**: Easy addition of new technical indicators
- **Signal Rules**: Configurable combination logic
- **Risk Models**: Pluggable risk management modules
- **Data Sources**: Multiple data provider integration

## Security and Reliability

### Security Measures
- **Token Management**: Secure storage and automatic renewal
- **API Rate Limiting**: Respect TCBS API limits
- **Input Validation**: Data sanitization and validation
- **Error Isolation**: Graceful error handling

### Reliability Features
- **Data Persistence**: Automatic caching and backup
- **Connection Recovery**: Automatic reconnection on failures
- **State Management**: Consistent state across restarts
- **Monitoring**: Health checks and alerting

This architecture provides a robust, scalable, and maintainable foundation for automated stock trading in Vietnamese markets.
