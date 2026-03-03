# VN30 Futures Trading System V2 - Refactored

## Overview

This is a completely refactored version of the VN30 futures trading system with unified code structure, eliminating duplications and improving maintainability. The system implements pairs trading between VN30F1M and VN30F2M using statistical arbitrage.

## Key Improvements Over V1

### 🔧 **Code Unification**
- **Eliminated Duplications**: Removed 200+ lines of duplicated code
- **Unified Token Management**: Single `TokenManager` class handles all authentication
- **Base WebSocket Classes**: Consolidated 4 similar WebSocket implementations
- **Centralized Position Management**: Single `PositionManager` for all position operations
- **Unified Utilities**: Common functions moved to `utils` package

### 🏗️ **Improved Architecture**
- **Modular Design**: Clear separation of concerns with dedicated packages
- **Enhanced Error Handling**: Comprehensive exception handling throughout
- **Better Logging**: Structured logging with `LoggerManager`
- **Type Hints**: Full type annotations for better code clarity

### 📁 **New Project Structure**
```
open_api_trading_v2/
├── core/                    # Core trading components
│   ├── api_client.py       # Unified TCBS API client
│   ├── streaming_data_handler.py
│   ├── processing_strategy.py
│   └── order_monitor.py
├── utils/                   # Unified utility functions
│   ├── common.py           # Common utilities
│   ├── token_manager.py    # Token management
│   └── position_manager.py # Position handling
├── ws_clients/             # WebSocket base classes
│   └── base_websocket.py   # Unified WebSocket clients
├── logger_utils/           # Enhanced logging system
│   └── fast_logger.py      # Improved async logging
├── data/                   # Data management
│   └── defaults.py         # Default file creation
├── config/                 # Configuration files
│   ├── stock_config.yaml   # Stock trading configuration
│   ├── futures_config.yaml # Futures trading configuration
│   └── credentials.yaml    # Your API credentials (gitignored)
└── runners/run_futures_strategy.py                 # Entry point
```

### 🧾 Logs Layout

All runtime logs are written under the single parent `logs/` directory with a clear hierarchy. Example structure:

```
logs/
├── Main/
│   └── main.log
├── Stock Strategy/
│   └── trading.log
├── Futures/
│   ├── Trading/
│   │   └── trading.txt
│   ├── Trade History/
│   │   └── trade_history.txt
│   └── Messages/
│       ├── F1M/
│       │   └── f1m_messages.txt
│       └── F2M/
│           └── f2m_messages.txt
```

This replaces the older scattered top-level folders like `F1M Logging/`, `F2M Logging/`, `Trade History Logging/`, and `Trading Logging/`.

## Installation & Setup

### Prerequisites
```bash
pip3 install pandas openpyxl asyncio websockets aiohttp requests numpy
```

### Quick Start
1. **Navigate to V2 directory**:
   ```bash
   cd open_api_trading_v2
   ```

2. **Initialize default files**:
   ```bash
   python3 data/defaults.py
   ```

3. **Update config/token.json** with your actual TCBS token

4. **Run the system**:
   ```bash
   python3 runners/run_futures_strategy.py
   ```

## Key Features

### 🔐 **Enhanced Token Management**
```python
from utils.token_manager import TokenManager

token_manager = TokenManager()
if token_manager.is_token_valid():
    token = token_manager.load_token()
```

### 📊 **Unified Position Management**
```python
from utils.position_manager import PositionManager

pos_manager = PositionManager(client, ['VN30F2509', '41I1FA000'])
positions = pos_manager.get_positions()
total_position = pos_manager.get_total_position()
```

### 🌐 **Base WebSocket Classes**
```python
from websockets.base_websocket import DerivativeStreamingClient

client = DerivativeStreamingClient(['VN30F2509', '41I1FA000'])
await client.connect_with_retry(token)
```

### 📝 **Enhanced Logging**
```python
from logging.fast_logger import get_logger

logger = get_logger('trading', 'Trading Logging')
await logger.log("Trade executed", "INFO")
await logger.log_error("Connection failed")
```

## Configuration

### Trading Parameters (`config.py`)
```python
# Instruments
ticker_f1m = 'VN30F2509'
ticker_f2m = '41I1FA000'

# Risk Management
max_position = 10
cut_points = 20
cut_time = 60

# DCA Configuration
avg_price_config = {4: 1.0, 6: 1.8, 8: 3.5, 9: 5.0}
```

## Utilities Available

### Common Functions (`utils/common.py`)
- `is_within_time_range()` - Trading hours validation
- `parse_positions()` - Position data parsing
- `calculate_required_margin()` - Margin calculations
- `save_json_async()` - Async JSON operations

### Token Management (`utils/token_manager.py`)
- `load_token()` - Load and validate tokens
- `renew_token()` - OTP-based renewal
- `get_valid_token()` - Get valid token with auto-renewal

### Position Management (`utils/position_manager.py`)
- `get_positions()` - Retrieve current positions
- `get_total_position()` - Sum of all positions
- `get_position_summary()` - Formatted position display

## WebSocket Clients

### Base Classes (`websockets/base_websocket.py`)
- `BaseWebSocketClient` - Common WebSocket functionality
- `DerivativeStreamingClient` - Derivative market data
- `OrderChangeStreamingClient` - Order status updates
- `StockStreamingClient` - Stock market data

## Logging System

### Enhanced Features (`logging/fast_logger.py`)
- **Structured Logging**: Timestamps and log levels
- **Auto-flush**: Based on buffer size or time interval
- **Error Handling**: Graceful failure handling
- **Multiple Loggers**: Centralized logger management

### Usage Examples
```python
# Get logger for specific component
logger = get_logger('trading', 'Trading Logging')

# Different log levels
await logger.log("System started", "INFO")
await logger.log_warning("High volatility detected")
await logger.log_error("Connection failed")
await logger.log_debug("Debug information")

# Force flush
await logger.flush()
```

## Migration from V1

### What's Different
1. **Import Changes**: Use new package structure
2. **Token Handling**: Use `TokenManager` instead of manual file operations
3. **Position Retrieval**: Use `PositionManager` instead of direct API calls
4. **WebSocket Connections**: Inherit from base classes
5. **Logging**: Use structured logging system

### Migration Steps
1. **Copy Data Files**: Your existing `config/token.json`, `config/spread_dca.json`, and `data/tick_data.json` are automatically organized
2. **Update Configuration**: Modify `config.py` if needed
3. **Test System**: Run in parallel with V1 to verify functionality

## Monitoring & Debugging

### Enhanced Monitoring
- **State Transition Logging**: Detailed order state tracking
- **Performance Metrics**: Buffer sizes, connection status
- **Error Categorization**: Structured error reporting

### Debug Mode
Enable detailed logging by modifying flush intervals:
```python
logger = get_logger('debug', flush_interval=1)
```

## Error Handling

### Improved Resilience
- **Connection Retry Logic**: Automatic reconnection with exponential backoff
- **Graceful Degradation**: Fallback to cached data on API failures
- **Exception Isolation**: Errors in one component don't crash the system

## Performance Improvements

### Optimizations
- **Reduced Memory Usage**: Efficient data structures
- **Faster Startup**: Parallel initialization
- **Better Resource Management**: Proper cleanup and connection pooling

## Testing

### Validation Tools
```bash
# Test token validity
python3 -c "from utils.token_manager import TokenManager; print(TokenManager().is_token_valid())"

# Test position retrieval
python3 -c "from utils.position_manager import PositionManager; from core.api_client import TCBSClient; client = TCBSClient(); client.initialize_token(); pm = PositionManager(client, ['VN30F2509']); print(pm.get_positions())"

# Test logging system
python3 -c "import asyncio; from logging.fast_logger import get_logger; logger = get_logger('test'); asyncio.run(logger.log('Test message'))"
```

## Troubleshooting

### Common Issues
1. **Import Errors**: Ensure you're in the `open_api_trading_v2` directory
2. **Token Issues**: Use `TokenManager` methods for token validation
3. **Connection Problems**: Check WebSocket base class error messages
4. **Position Mismatches**: Use `PositionManager.get_position_summary()` for debugging

### Debug Commands
```bash
# Check system health
python3 -c "from data.defaults import create_default_files; create_default_files()"

# Validate configuration
python3 -c "import config; print('Config loaded successfully')"
```

## Advantages Over V1

| Feature | V1 | V2 |
|---------|----|----|
| Code Duplication | 200+ duplicated lines | Eliminated |
| Token Management | 3 separate implementations | Unified `TokenManager` |
| WebSocket Clients | 4 similar classes | Base class inheritance |
| Position Handling | 5+ repeated code blocks | Single `PositionManager` |
| Error Handling | Basic try/catch | Comprehensive exception handling |
| Logging | Simple file writes | Structured async logging |
| Type Safety | No type hints | Full type annotations |
| Testing | Manual testing only | Built-in validation tools |

## Stock Trading Features (NEW)

### 📈 **Technical Indicator Framework**
- **TA-Lib Integration**: Industry-standard indicators (RSI, SMA, EMA, MACD, Bollinger Bands)
- **Custom Indicators**: Fallback implementations without TA-Lib dependency
- **Signal Generation**: Combine multiple indicators with configurable logic
- **Real-time Updates**: Streaming price integration with historical data

### 🎯 **Trading Strategy System**
- **Multi-Symbol Support**: Trade multiple Vietnamese stocks simultaneously
- **Risk Management**: Position sizing, stop-loss, take-profit automation
- **Signal Rules**: Configurable buy/sell conditions (RSI < 30 + Price > MA20)
- **Portfolio Management**: Cash balance, buying power, position tracking

### 📊 **Data Management**
- **Historical Data**: Automatic caching and persistence
- **Real-time Integration**: Combine streaming prices with historical data
- **Indicator Calculation**: Efficient data structures for technical analysis
- **Performance Optimization**: Vectorized calculations and caching

### 🔧 **Usage Examples**
```python
# Basic indicator usage
rsi = RSI(period=14, oversold=30, overbought=70)
result = rsi.calculate(price_data)
signals = result.signals  # Buy/sell signals

# Combined signal generation
signal_gen = SignalGenerator()
signal_gen.add_indicator("RSI", rsi)
signal_gen.add_indicator("SMA", SMA(period=20))

# Custom rule: Buy when RSI < 30 AND price > SMA
rule = SignalRule(
    name="RSI_SMA_BUY",
    indicators=["RSI", "SMA"],
    conditions={
        "RSI": {"signal_type": SignalType.BUY, "min_strength": 0.3},
        "SMA": {"signal_type": SignalType.BUY, "min_strength": 0.2}
    },
    logic=CombinationLogic.AND
)
```

### 🚀 **Getting Started with Stock Trading**

#### 1. Install Dependencies
```bash
pip install -r requirements.txt
# Optional: pip install TA-Lib  # For advanced indicators
```

#### 2. Set Up Credentials (One-time setup)
```bash
# Interactive setup
python runners/setup_credentials.py

# Or manually copy and edit
cp config/credentials.yaml.example config/credentials.yaml
# Edit config/credentials.yaml with your TCBS API credentials
```

#### 3. Test Configuration
```bash
# Test all configuration components
python runners/test_configuration.py

# Test indicators
python runners/test_indicators.py
```

#### 4. Run Trading Strategy
```bash
# Validate setup
python runners/run_stock_strategy.py --validate

# Run strategy (dry-run)
python runners/run_stock_strategy.py --dry-run

# Run with real account
python runners/run_stock_strategy.py --account YOUR_ACCOUNT_NO
```

## Future Enhancements

The unified structure makes it easier to implement:
- **Machine Learning Integration**: Centralized data handling
- **Real-time Dashboards**: Structured logging output
- **Advanced Risk Management**: Modular risk components
- **Multi-Asset Support**: Extensible base classes
- **Cloud Deployment**: Containerized components

## License & Disclaimer

This is an educational refactoring project. The original V1 system remains unchanged and functional. Use V2 for improved maintainability and future development.

---

**Note**: This V2 system is a complete rewrite focused on code quality and maintainability. Your original V1 system continues to run independently without any modifications.
