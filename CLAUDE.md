# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Algorithmic trading system integrated with the Vietnamese TCBS brokerage API. Supports historical backtesting, live market scanning, and paper/live order execution for equities and futures.

## Common Commands

```bash
# Run market scanner (main entry point for V2 system)
python trading_on_tcbs_api/stock_system_v2/scripts/scan_market.py

# Run backtest across all symbols
python trading_on_tcbs_api/stock_system_v2/scripts/backtest_market.py

# Run the auto-trader (live trading loop)
python trading_on_tcbs_api/stock_system_v2/main.py

# Run legacy stock strategy
python trading_on_tcbs_api/runners/run_stock_strategy.py

# Run tests
python -m pytest test_tcbs.py test_vci.py test_requests.py test_other_sources.py

# Setup credentials (first-time setup)
python trading_on_tcbs_api/runners/setup_credentials.py

# Validate configuration
python trading_on_tcbs_api/runners/test_configuration.py
```

## Architecture

### V2 System (Primary) — `trading_on_tcbs_api/stock_system_v2/`

The modern production system. All new strategies and features should go here.

**Data flow:**
1. `data_ingest/data_provider.py` — fetches historical OHLCV from vnstock (KBS source), caches to CSV, merges with live TCBS prices into a unified DataFrame
2. `core/indicator_engine.py` — computes all technical indicators (SMA, EMA, RSI, MACD, ROC, Volume MA) in a single pandas-ta pass over the DataFrame
3. `core/market_scanner.py` — iterates symbols, applies indicator engine, runs all strategies, returns today's signals as dict/DataFrame
4. `execution/order_manager.py` — places orders; **safe mode is enabled by default** (dry run), must be explicitly disabled for live trading
5. `execution/trade_manager.py` — paper trading simulator tracking positions, cash, and PnL

**Key classes:**
- `StockAuth` (`auth/auth.py`) — loads/saves JWT from `config/token.json`, renews via OTP + API key
- `AccountManager` (`finance/account_manager.py`) — starts with 100M VND mock balance; can sync real assets from TCBS API
- `AutoTrader` (`core/auto_trader.py`) — orchestrates full pipeline: auth → strategies → scanner → orders

### Strategy Framework

All strategies live in `stock_system_v2/strategies/` and must inherit from `SignalStrategy` (`strategies/strategy.py`):

```python
class MyStrategy(SignalStrategy):
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # Must add a 'signal' column: 1 (BUY), -1 (SELL), 0 (HOLD)
        return df
```

`CombinedStrategy` (`combined_strategy.py`) aggregates multiple strategies with AND/OR logic for entry/exit. Existing strategies: `SimpleMAStrategy`, `RSIStrategy`, `VolumeBoomStrategy`, `IntradayDipStrategy`, `DipBuyStrategy`, `CumulativeDropStrategy`, `RSIDivergenceStrategy`.

### Configuration

- `trading_on_tcbs_api/config/credentials.yaml` — TCBS API key, account IDs, token path (copy from `credentials.yaml.example`)
- `stock_system_v2/config.py` — default symbol universe (TCB, HPG, SSI, VHM, VIC, VRE, VNM, FPT), risk params (10% position size, 5% stop loss, 10% take profit)
- `config/stock_config.yaml` / `futures_config.yaml` — legacy runner configurations

### Legacy Systems

- `stock_strategy/` — older equity trading system with its own data manager
- `futures_strategy/` — futures with WebSocket streaming data
- `simple_wow/` — async order placement system with its own strategy layer
- `indicators/` — TA-Lib based indicator library with `SignalType` enum (BUY/SELL/HOLD/STRONG_BUY/STRONG_SELL)

New work should target the V2 system; the legacy modules are in maintenance mode.

### Async Patterns

Core infrastructure (`core/api_client.py`, `ws_clients/`, `simple_wow/`) uses `asyncio`. The V2 system is synchronous with async helpers for non-blocking API calls. Use `aiohttp` for async HTTP; `requests` for sync calls.

## Key Dependencies

- `vnstock` — historical OHLCV data (KBS source configured in `data_provider.py`)
- `pandas-ta` — vectorized technical indicator computation
- `TA-Lib` — used in legacy `indicators/` module
- `PyYAML` — configuration loading
- `aiohttp` / `websockets` — async TCBS API and WebSocket clients
