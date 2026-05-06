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

#### Local Data Paths (Machine-Specific Override)

`trading_on_tcbs_api/config/local_config.json` overrides `DATA_DIR` and `EXPORT_DIR` at runtime. This file is **not committed** and must be created manually on each machine. On the primary dev machine, both paths point to Google Drive so cached stock CSVs and backtest exports are accessible from anywhere:

```json
{
    "DATA_DIR": "/Users/namng/Library/CloudStorage/GoogleDrive-nam.n.g.93@gmail.com/My Drive/PythonProject/data/stocks",
    "EXPORT_DIR": "/Users/namng/Library/CloudStorage/GoogleDrive-nam.n.g.93@gmail.com/My Drive/PythonProject/data/exports"
}
```

- `DATA_DIR` — cached historical OHLCV CSVs, one file per symbol (`{SYMBOL}_1D.csv`). This is where `DataProvider` reads/writes its cache, so if this directory looks empty locally, check Google Drive.
- `EXPORT_DIR` — backtest result CSVs written by scan/backtest scripts.
- Without `local_config.json`, both paths fall back to `trading_on_tcbs_api/data/stocks` and `trading_on_tcbs_api/data/exports` inside the repo.

### Legacy Systems

- `stock_strategy/` — older equity trading system with its own data manager
- `futures_strategy/` — futures with WebSocket streaming data
- `simple_wow/` — async order placement system with its own strategy layer
- `indicators/` — TA-Lib based indicator library with `SignalType` enum (BUY/SELL/HOLD/STRONG_BUY/STRONG_SELL)

New work should target the V2 system; the legacy modules are in maintenance mode.

### Async Patterns

Core infrastructure (`core/api_client.py`, `ws_clients/`, `simple_wow/`) uses `asyncio`. The V2 system is synchronous with async helpers for non-blocking API calls. Use `aiohttp` for async HTTP; `requests` for sync calls.

## Codebase Map

Full file tree with one-line descriptions. Use this to locate code; cross-reference the Architecture section above for how the modules fit together.

```
trading_on_tcbs_api/
├── __init__.py
├── test_signals.py                          # ad-hoc signal sanity checks
│
├── config/                                  # runtime config & secrets (most files gitignored)
│   ├── credentials.yaml                     # TCBS API key + account IDs
│   ├── token.json                           # cached JWT (renewed by StockAuth)
│   ├── profile.json                         # cached user profile from TCBS
│   ├── local_config.json                    # machine-specific DATA_DIR / EXPORT_DIR override
│   ├── stock_config.yaml                    # legacy stock runner config
│   └── futures_config.yaml                  # legacy futures runner config
│
├── core/                                    # legacy shared infra (used by simple_wow + futures)
│   ├── api_client.py                        # async aiohttp wrapper for TCBS REST
│   └── order_monitor.py                     # polls order status post-submission
│
├── ws_clients/                              # legacy WebSocket clients
│   └── base_websocket.py                    # base class for streaming connections
│
├── utils/                                   # cross-cutting helpers (shared by V1 + V2)
│   ├── common.py                            # generic helpers (timestamps, formatting)
│   ├── config_manager.py                    # YAML loader for legacy configs
│   ├── token_manager.py                     # JWT persistence helpers
│   └── position_manager.py                  # position math used by older runners
│
├── logger_utils/
│   └── fast_logger.py                       # structured logger w/ rotating files in logs/
│
├── indicators/                              # LEGACY: TA-Lib indicator suite (V2 uses pandas-ta)
│   ├── base.py                              # SignalType enum, base indicator class
│   ├── talib_indicators.py                  # TA-Lib wrappers (RSI, MACD, BB, etc.)
│   ├── custom_indicators.py                 # custom/composite indicators
│   └── signal_generator.py                  # turns indicator outputs into BUY/SELL signals
│
├── runners/                                 # CLI entry points for legacy systems + setup
│   ├── run_stock_strategy.py                # legacy stock loop
│   ├── run_futures_strategy.py              # legacy futures loop
│   ├── setup_credentials.py                 # first-time creds wizard
│   ├── test_configuration.py                # sanity-check creds + config files
│   └── test_indicators.py                   # smoke tests for legacy indicators
│
├── stock_strategy/                          # LEGACY equity system (maintenance only)
│   ├── strategy.py                          # legacy strategy class
│   └── data_manager.py                      # legacy OHLCV fetch/cache layer
│
├── futures_strategy/                        # LEGACY futures system (maintenance only)
│   ├── streaming_data_handler.py            # WebSocket tick handler
│   └── processing_strategy.py               # futures signal logic
│
├── simple_wow/                              # LEGACY async order placement framework
│   ├── main.py                              # async runner
│   ├── trading_asyncio_module.py            # asyncio order placement engine
│   ├── smart_order_manager.py               # order lifecycle management
│   ├── signal_generator.py / signal_generator_2.py  # signal pipelines
│   ├── config_manager.py                    # YAML config loader (this module's own)
│   ├── strategy_config.yaml / credentials.yaml      # local configs
│   └── strategies/
│       ├── base_strategy.py
│       └── rsi_strategy.py
│
└── stock_system_v2/                         # ★ PRIMARY production system — new work goes here
    ├── main.py                              # AutoTrader entry point (live loop)
    ├── config.py                            # symbol universe + risk params
    │
    ├── auth/
    │   └── auth.py                          # StockAuth: JWT load/save + OTP renewal
    │
    ├── data_ingest/
    │   └── data_provider.py                 # vnstock (KBS) historical fetch + CSV cache + live merge
    │
    ├── core/
    │   ├── stock_api_client.py              # sync TCBS REST client (V2)
    │   ├── indicator_engine.py              # single-pass pandas-ta indicator computation
    │   ├── market_scanner.py                # iterates symbols × strategies → today's signals
    │   ├── backtester.py                    # historical strategy simulation engine
    │   └── auto_trader.py                   # orchestrator: auth → scan → execute
    │
    ├── strategies/                          # all V2 strategies inherit SignalStrategy
    │   ├── strategy.py                      # SignalStrategy base class
    │   ├── combined_strategy.py             # AND/OR aggregation of multiple strategies
    │   ├── ma_strategy.py                   # SimpleMAStrategy
    │   ├── rsi_strategy.py                  # RSIStrategy
    │   ├── rsi_divergence_strategy.py       # RSIDivergenceStrategy (unverified, see commit history)
    │   ├── volume_strategy.py               # VolumeBoomStrategy
    │   ├── intraday_dip_strategy.py         # IntradayDipStrategy
    │   ├── dip_buy_strategy.py              # DipBuyStrategy
    │   └── cumulative_drop_strategy.py      # CumulativeDropStrategy
    │
    ├── execution/
    │   ├── order_manager.py                 # places live/paper orders (safe-mode default ON)
    │   ├── order_tracker.py                 # tracks open orders + fills
    │   └── trade_manager.py                 # paper trading simulator (positions, cash, PnL)
    │
    ├── finance/
    │   ├── account_manager.py               # mock 100M VND balance; can sync real TCBS assets
    │   └── performance_analyzer.py          # PnL / drawdown / win-rate metrics
    │
    ├── scripts/                             # operator-facing CLI tools (run directly)
    │   │  # — main entry points —
    │   ├── scan_market.py                   # ★ daily live signal scan
    │   ├── backtest_market.py               # ★ full-universe backtest
    │   ├── backtest_intraday_dip.py         # backtest intraday dip strategy
    │   ├── backtest_weekly_top3.py          # weekly top-3 momentum backtest
    │   ├── screen_dip_stocks.py             # one-off dip screener
    │   ├── crisis_hedge_calculator.py       # short-gamma hedge sizing helper
    │   │  # — analytics / visualization —
    │   ├── analyze_performance.py
    │   ├── view_portfolio.py
    │   ├── visualize_trades.py
    │   │  # — verification suite (run after changes) —
    │   ├── verify_backtest.py
    │   ├── verify_data_provider.py
    │   ├── verify_live_price.py
    │   ├── verify_account.py
    │   ├── verify_analytics.py
    │   ├── verify_order.py
    │   │  # — probes (manual API exploration; not part of pipeline) —
    │   ├── probe_history.py / probe_signal.py / probe_profile.py
    │   ├── probe_assets.py / probe_vnstock.py
    │   │  # — misc test/utility scripts —
    │   ├── fetch_real_assets.py             # pulls real TCBS holdings into AccountManager
    │   ├── test_real_account.py / test_live_sync.py / test_endpoint.py / test_vnstock_vci.py
    │   └── logs/                            # per-script log output
    │
    ├── exports/                             # default backtest output dir (overridable via EXPORT_DIR)
    └── data/                                # default cache dir (overridable via DATA_DIR)

docs/
└── tcbs_openapi.json                        # captured TCBS OpenAPI spec for reference

logs/                                        # rotating log files written by fast_logger
```

**Quick navigation tips:**
- New strategy → drop in `stock_system_v2/strategies/`, register in `combined_strategy.py` or call sites.
- New indicator → extend `core/indicator_engine.py` (avoid TA-Lib; the V2 system is pandas-ta).
- API issue → `auth/auth.py` (token) → `core/stock_api_client.py` (REST) → check `docs/tcbs_openapi.json`.
- Anything in `stock_strategy/`, `futures_strategy/`, `simple_wow/`, `indicators/`, `core/` (top-level), `ws_clients/` is **legacy**; do not extend, only patch.

## Key Dependencies

- `vnstock` — historical OHLCV data (KBS source configured in `data_provider.py`)
- `pandas-ta` — vectorized technical indicator computation
- `TA-Lib` — used in legacy `indicators/` module
- `PyYAML` — configuration loading
- `aiohttp` / `websockets` — async TCBS API and WebSocket clients
