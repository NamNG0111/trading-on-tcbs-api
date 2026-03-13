---
name: backtest_strategy
description: Run a complete backtest lifecycle for any trading strategy — from configuration, simulation, signal export, to candlestick visualization. Use this skill when the user asks to backtest, evaluate, or verify a strategy's historical performance.
---

# Skill: Backtest a Trading Strategy

## When to Use This Skill

Activate this skill when the user requests any of the following:
- "Backtest this strategy", "How profitable is this strategy?", "Test it on FPT/HPG/..."
- "Show me where the signals appear on the chart"
- "Export the detailed signal log"
- "Compare strategy X vs strategy Y"

---

## Prerequisites

Before executing, verify:
1. The strategy class exists in `stock_system_v2/strategies/` and is registered in `__init__.py`
2. Any custom indicators the strategy depends on are configured in `core/indicator_engine.py`
3. The `mplfinance` package is installed (for visualization)

If a strategy does NOT exist yet, **stop** and use the `/add_strategy_or_indicator` workflow first.

---

## Architecture Context

> **CRITICAL**: The AI assistant MUST understand these system invariants before making any changes.

### Data Flow
```
DataProvider → IndicatorEngine → Strategy.generate_signals() → Backtester.run()
```

### File Map
| Component | Path | Purpose |
|:--|:--|:--|
| Base class | `strategies/strategy.py` | `SignalStrategy` ABC — all strategies inherit this |
| Strategy registry | `strategies/__init__.py` | Public exports for all strategy classes |
| Indicator engine | `core/indicator_engine.py` | Centralized `pandas-ta` computation (SMA, RSI, ROC, etc.) |
| Backtester engine | `core/backtester.py` | Simulation loop, forward returns, fixed-hold portfolios |
| CLI script | `scripts/backtest_market.py` | Market-wide aggregation + CSV export |
| Visualizer | `scripts/visualize_trades.py` | Candlestick chart with BUY/SELL markers |
| Signal exports | `exports/` | Auto-generated CSV files per strategy |

### Key Rules
1. **Never compute indicators inside a strategy class.** All math is pre-computed by `IndicatorEngine`.
2. **Column names are always lowercase.** `pandas-ta` outputs `SMA_20` → engine lowercases to `sma_20`.
3. **Signals are integers**: `1` = BUY, `-1` = SELL, `0` = HOLD.
4. Strategies with no SELL logic must be wrapped in `CombinedStrategy` with explicit `sell_strategies=[]`.

---

## Execution Steps

### Step 1: Configure the Backtest

Open `scripts/backtest_market.py` and set the configuration block at the top:

```python
# ==========================================
# BACKTEST CONFIGURATION
# ==========================================
INITIAL_CAPITAL = 1_000_000_000  # 1 Billion VND
TEST_DAYS = 1825                 # 5 Years

# Analysis Modules — toggle True/False
SHOW_PORTFOLIO_SUMMARY = True    # Table 1: Standard BUY+SELL execution
SHOW_FORWARD_RETURNS = True      # Table 2: N-day mathematical returns
SHOW_FIXED_HOLD = True           # Table 3: Chronological time-based exits
FORWARD_DAYS = [3, 5, 10, 20]
# ==========================================
```

### Step 2: Register the Strategy in the Script

Inside `backtest_market.py`'s `main()` function, instantiate the strategy and add it to `my_strategies`:

```python
# Example: Adding a new BollingerBand strategy
from trading_on_tcbs_api.stock_system_v2.strategies import BollingerStrategy

bb_buy = BollingerStrategy(period=20, std_dev=2.0)
strat_bb = CombinedStrategy(
    strategies=[],
    buy_strategies=[bb_buy],
    sell_strategies=[sma_exit_basic],  # Reuse existing exit
    buy_mode="AND",
    sell_mode="OR"
)

my_strategies[f"Bollinger ({bb_buy.period}, {bb_buy.std_dev}σ)"] = strat_bb
```

> **IMPORTANT**: Also add the same strategy block to `scripts/visualize_trades.py` if the user wants chart visualization.

### Step 3: Run the Backtest

```bash
# Full VN30 market scan
python3 -m trading_on_tcbs_api.stock_system_v2.scripts.backtest_market

# Specific stocks only
python3 -m trading_on_tcbs_api.stock_system_v2.scripts.backtest_market FPT,HPG,TCB
```

### Step 4: Inspect Detailed Signals

After running, check the auto-exported CSV files:
```
stock_system_v2/exports/<StrategyName>_signals.csv
```

Each CSV contains one row per BUY signal with columns:
- `Ticker`, `time`, `close`, `volume`
- All indicator values at that moment (`rsi_14`, `sma_20`, etc.)
- `Return_3D_pct`, `Return_5D_pct`, `Return_10D_pct`, `Return_20D_pct`

### Step 5: Visualize on Candlestick Chart

```bash
python3 -m trading_on_tcbs_api.stock_system_v2.scripts.visualize_trades FPT "Strategy Name"
```

The chart renders:
- 🟢 Green `^` arrows = BUY signals
- 🔴 Red `v` arrows = SELL signals
- Dark theme (`nightclouds` style) with volume bars

---

## Interpreting Results

### Table 1: Portfolio Summary
| Metric | Good Sign | Bad Sign |
|:--|:--|:--|
| Avg Return (%) | > 5% | Negative |
| Win Rate (%) | > 55% | < 40% |
| Max Drawdown (%) | > -20% | < -40% |
| Profit Factor | > 1.5 | < 1.0 |

### Table 2: Forward Returns
Shows the **mathematical** return if you held exactly N days after every BUY signal (infinite capital assumption).
- High Win Rate + Positive Mean = Strategy identifies genuine dips
- Negative Median with Positive Mean = A few big winners skewing results (risky)

### Table 3: Fixed Hold Portfolio
Shows **real portfolio** performance with 1 account trading chronologically.
- Compare vs Table 2 to see the impact of missed signals (capital locked up)
- High "Avg Trades / Stock" = Strategy fires frequently

---

## Troubleshooting

| Problem | Cause | Fix |
|:--|:--|:--|
| `ValueError: Missing required indicator column` | Indicator not in `IndicatorEngine` | Add the indicator to `get_default_config()` and `append_indicators()` |
| Only 1 BUY marker on chart | Strategy has no SELL logic, backtester holds forever | The visualizer uses `allow_multiple_buys=True` — verify this flag is set |
| CSV export is empty | No BUY signals generated | Check strategy logic or widen thresholds |
| `ModuleNotFoundError` | Strategy not registered | Add import to `strategies/__init__.py` |

---

## Quick Reference: Available Strategies

| Name | Class | Key Parameters |
|:--|:--|:--|
| DipBuy | `DipBuyStrategy` | `sma_window`, `drop_pct` |
| Volume Breakout | `VolumeBoomStrategy` | `window`, `threshold_pct` |
| RSI | `RSIStrategy` | `period`, `oversold`, `overbought`, `is_reversal` |
| Cumulative Drop | `CumulativeDropStrategy` | `days`, `drop_pct` |
| SMA Crossover | `SimpleMAStrategy` | `short_window`, `long_window`, `invert` |
| Combined | `CombinedStrategy` | `buy_strategies`, `sell_strategies`, `buy_mode`, `sell_mode` |
