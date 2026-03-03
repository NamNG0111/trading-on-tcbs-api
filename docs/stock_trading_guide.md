# Stock Trading System Guide

## 🎯 Overview

This guide covers the new stock trading capabilities added to the VN30 futures trading system. The stock trading framework provides technical indicator-based trading with comprehensive risk management for Vietnamese stock markets.

## 🚀 Quick Start

### 1. Install Dependencies
```bash
# Core dependencies (already installed)
pip install asyncio aiohttp websockets numpy pandas

# Additional for stock trading
pip install aiofiles python-dateutil

# Optional: TA-Lib for advanced indicators
pip install TA-Lib
```

### 2. Validate Setup
```bash
python runners/run_stock_strategy.py --validate
```

### 3. Test Indicators
```bash
python runners/test_indicators.py
```

### 4. Run Strategy (Dry Run)
```bash
python runners/run_stock_strategy.py --dry-run
```

### 5. Run with Real Account
```bash
python runners/run_stock_strategy.py --account YOUR_TCBS_ACCOUNT_NO
```

## 📊 Technical Indicators

### Available Indicators

#### TA-Lib Indicators (Recommended)
- **RSI**: Relative Strength Index
- **SMA**: Simple Moving Average  
- **EMA**: Exponential Moving Average
- **MACD**: Moving Average Convergence Divergence
- **Bollinger Bands**: Price volatility bands
- **Stochastic**: Momentum oscillator

#### Custom Indicators (Fallback)
- **Custom RSI**: Pure Python implementation
- **Custom SMA/EMA**: Moving averages without TA-Lib
- **Price Momentum**: Rate of price change
- **Volatility**: Price volatility measure

### Usage Examples

```python
from indicators.talib_indicators import RSI, SMA
from indicators.custom_indicators import CustomRSI

# TA-Lib RSI
rsi = RSI(period=14, oversold=30, overbought=70)
result = rsi.calculate(price_data)

# Custom RSI (fallback)
custom_rsi = CustomRSI(period=14, oversold=30, overbought=70)
result = custom_rsi.calculate(price_data)

# Check signals
for signal in result.signals:
    print(f"{signal.signal_type.value}: {signal.strength:.2f}")
```

## 🎯 Signal Generation

### Signal Rules

The system supports multiple signal combination strategies:

#### 1. Single Indicator Rules
```python
from indicators.signal_generator import SignalGenerator, SignalRule

signal_gen = SignalGenerator()
signal_gen.add_indicator("RSI", RSI(period=14))

# RSI oversold/overbought signals
signals = signal_gen.generate_signals({"RSI": price_data}, current_price)
```

#### 2. Combined Indicator Rules
```python
# RSI + SMA combination
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

#### 3. Weighted Combinations
```python
weighted_rule = SignalRule(
    name="WEIGHTED_SIGNALS",
    indicators=["RSI", "SMA", "MACD"],
    logic=CombinationLogic.WEIGHTED,
    weights={"RSI": 0.5, "SMA": 0.3, "MACD": 0.2}
)
```

### Pre-built Signal Rules

```python
from indicators.signal_generator import CommonSignalRules

# Use common patterns
rsi_rule = CommonSignalRules.rsi_oversold_overbought()
combo_rule = CommonSignalRules.rsi_ma_combo()
macd_rule = CommonSignalRules.macd_crossover()
```

## 💼 Trading Strategy

### Configuration

Edit `config/stock_trading_config.json`:

```json
{
  "symbols": ["VIC", "VHM", "VNM", "SAB", "MSN"],
  "max_position_per_symbol": 1000,
  "max_portfolio_value": 2000000000,
  "risk_per_trade": 0.02,
  "stop_loss_pct": 0.05,
  "take_profit_pct": 0.10,
  "min_signal_strength": 0.4,
  "trading_hours": [[9, 0], [15, 0]],
  "data_update_interval": 60
}
```

### Strategy Features

- **Multi-Symbol Trading**: Trade multiple stocks simultaneously
- **Risk Management**: Automatic position sizing based on portfolio risk
- **Stop Loss/Take Profit**: Configurable exit strategies
- **Trading Hours**: Respects Vietnamese market hours
- **Real-time Data**: Integrates streaming prices with historical data
- **Signal Filtering**: Only trades signals above minimum strength threshold

### Manual Strategy Usage

```python
from core.stock_trading_strategy import StockTradingStrategy, TradingConfig

# Create configuration
config = TradingConfig(
    symbols=["VIC", "VHM", "VNM"],
    max_position_per_symbol=1000,
    risk_per_trade=0.02
)

# Initialize strategy
strategy = StockTradingStrategy(config)
await strategy.initialize("YOUR_ACCOUNT_NO")

# Start trading
await strategy.start_trading()

# Check status
status = await strategy.get_strategy_status()
print(status)
```

## 📈 Data Management

### Historical Data

The system automatically manages historical data for indicator calculations:

```python
from data.historical_data_manager import HistoricalDataManager

# Create manager
hist_manager = HistoricalDataManager(data_dir="data/historical")

# Get historical data
data = await hist_manager.get_historical_data("VIC", days=100)

# Update with real-time price
updated_data = await hist_manager.update_with_realtime("VIC", current_price)
```

### Real-time Integration

```python
from data.historical_data_manager import RealTimeDataIntegrator

# Integrate streaming data
integrator = RealTimeDataIntegrator(hist_manager)
combined_data = await integrator.get_combined_data("VIC", current_price)
```

## 🔧 API Integration

### Stock Trading Client

```python
from core.stock_api_client import StockTradingClient

client = StockTradingClient()
await client.initialize("YOUR_ACCOUNT_NO")

# Place order
order_id = await client.place_stock_order("VIC", "BUY", 100, 85000)

# Check positions
positions = await client.get_stock_positions()

# Get cash balance
balance = await client.get_cash_balance()
```

### Available API Methods

- `place_stock_order()`: Place buy/sell orders
- `modify_stock_order()`: Modify existing orders
- `cancel_stock_order()`: Cancel orders
- `get_stock_orders()`: Get order history
- `get_stock_positions()`: Get current positions
- `get_cash_balance()`: Get available cash
- `get_buying_power()`: Get buying power
- `get_portfolio_summary()`: Get portfolio overview

## 🛡️ Risk Management

### Position Sizing

The system calculates position sizes based on:
- Portfolio value
- Risk per trade (% of portfolio)
- Stop loss percentage
- Current stock price

```python
# Automatic position sizing
position_size = strategy.calculate_position_size("VIC", 85000, 0.05)
```

### Risk Controls

- **Maximum position per symbol**: Prevents over-concentration
- **Portfolio value limits**: Prevents over-leveraging  
- **Stop loss automation**: Automatic exit on losses
- **Take profit targets**: Automatic profit taking
- **Trading hours validation**: Only trades during market hours
- **Signal strength filtering**: Only high-confidence signals

## 📊 Monitoring & Logging

### Strategy Status

```python
status = await strategy.get_strategy_status()
# Returns:
# - is_running: Strategy status
# - active_positions: Number of open positions
# - pending_orders: Number of pending orders
# - portfolio_value: Current portfolio value
# - cash_balance: Available cash
# - positions: Detailed position info
# - recent_signals: Recent trading signals
```

### Logging

The system uses structured async logging:
- Strategy decisions and reasoning
- Order placement and execution
- Signal generation details
- Risk management actions
- Error handling and recovery

Logs are stored in the `logs/` directory with timestamps and structured data.

## 🔍 Testing & Validation

### Component Testing

```bash
# Test all indicators
python runners/test_indicators.py

# Test individual components
python -c "
from indicators.custom_indicators import CustomRSI
rsi = CustomRSI(period=14)
result = rsi.calculate([100, 101, 102, 99, 98, 103])
print(f'RSI: {result.values[-1]:.2f}')
"
```

### Strategy Testing

```bash
# Dry run (no real trades)
python runners/run_stock_strategy.py --dry-run

# Validation mode
python runners/run_stock_strategy.py --validate

# Status check
python runners/run_stock_strategy.py --status --account YOUR_ACCOUNT
```

## 🚨 Common Issues & Solutions

### 1. TA-Lib Installation
```bash
# macOS with Homebrew
brew install ta-lib
pip install TA-Lib

# Ubuntu/Debian
sudo apt-get install libta-lib-dev
pip install TA-Lib

# If TA-Lib fails, custom indicators will be used automatically
```

### 2. Import Errors
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Check Python path includes project directory
- Verify no naming conflicts with installed packages

### 3. API Connection Issues
- Verify TCBS account credentials
- Check token expiration and renewal
- Ensure network connectivity
- Validate account permissions for stock trading

### 4. Data Issues
- Check historical data directory permissions
- Verify API endpoints are accessible
- Ensure sufficient disk space for data caching
- Check date/time formats match Vietnamese market

## 📚 Advanced Usage

### Custom Indicators

```python
from indicators.base import BaseIndicator, IndicatorResult, Signal

class MyCustomIndicator(BaseIndicator):
    def calculate(self, data, **kwargs):
        # Your calculation logic
        values = your_calculation(data)
        signals = self.generate_signals(values, data[-1])
        return IndicatorResult(values, signals, metadata)
    
    def generate_signals(self, values, current_price, **kwargs):
        # Your signal logic
        signals = []
        if values[-1] > threshold:
            signals.append(Signal(...))
        return signals

# Register your indicator
from indicators.base import register_indicator

@register_indicator("MY_INDICATOR")
class MyCustomIndicator(BaseIndicator):
    pass
```

### Custom Signal Rules

```python
from indicators.signal_generator import SignalRule, CombinationLogic

# Complex custom rule
custom_rule = SignalRule(
    name="COMPLEX_STRATEGY",
    indicators=["RSI", "SMA", "MACD", "VOLATILITY"],
    conditions={
        "RSI": {"signal_type": [SignalType.BUY], "min_strength": 0.4},
        "SMA": {"signal_type": [SignalType.BUY], "min_strength": 0.3},
        "MACD": {"signal_type": [SignalType.BUY], "min_strength": 0.2},
        "VOLATILITY": {"max_value": 0.05}  # Low volatility requirement
    },
    logic=CombinationLogic.WEIGHTED,
    weights={"RSI": 0.4, "SMA": 0.3, "MACD": 0.2, "VOLATILITY": 0.1},
    min_strength=0.5
)
```

## 🎯 Next Steps

1. **Backtest strategies** with historical data
2. **Implement machine learning** signal enhancement
3. **Add more indicators** (Ichimoku, Williams %R, etc.)
4. **Create portfolio optimization** algorithms
5. **Build real-time dashboard** for monitoring
6. **Add news sentiment analysis** integration
7. **Implement multi-timeframe** analysis

## 📞 Support

For issues or questions:
1. Check the logs in `logs/` directory
2. Run validation: `python runners/run_stock_strategy.py --validate`
3. Test components: `python runners/test_indicators.py`
4. Review configuration in `config/stock_trading_config.json`

The stock trading system is designed to be modular, extensible, and production-ready for Vietnamese stock markets.
