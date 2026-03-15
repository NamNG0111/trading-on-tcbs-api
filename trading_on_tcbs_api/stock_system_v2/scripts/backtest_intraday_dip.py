"""
Backtest Script: Intraday Dip-Buy Strategy.

Simulates the "market making" strategy on low-liquidity stocks:
- BUY when today's low drops ≥ x% below yesterday's close
- Simulated buy price = close_yesterday × (1 - x%) where x% = rolling percentile threshold
- SELL at today's close
- Each qualifying day = 1 independent trade

Usage:
    python3 -m trading_on_tcbs_api.stock_system_v2.scripts.backtest_intraday_dip
    python3 -m trading_on_tcbs_api.stock_system_v2.scripts.backtest_intraday_dip TCX
    python3 -m trading_on_tcbs_api.stock_system_v2.scripts.backtest_intraday_dip TCX,FPT,HPG
"""

import sys
import pandas as pd
import numpy as np
from trading_on_tcbs_api.stock_system_v2.data_ingest.data_provider import DataProvider
from trading_on_tcbs_api.stock_system_v2.core.indicator_engine import IndicatorEngine
from trading_on_tcbs_api.stock_system_v2.strategies import IntradayDipStrategy
from trading_on_tcbs_api.stock_system_v2.scripts.scan_market import VN30

# ==========================================
# BACKTEST CONFIGURATION
# ==========================================
HISTORY_DAYS = 250           # 1 years
LOOKBACK_DAYS = 250            # Rolling window for percentile calc (~1 year trading days)
PERCENTILE = 90.0             # Dip must exceed this percentile to trigger BUY
POSITION_SIZE = 100_000_000   # 100M VND per trade (for P&L estimation)
# ==========================================

DEFAULT_SYMBOLS = sorted(set(VN30 + ["TCX"]))


def backtest_single_stock(df: pd.DataFrame, symbol: str) -> dict:
    """
    Run custom P&L backtest for a single stock after signals are generated.
    
    Each BUY signal day = 1 independent intraday trade:
    - Buy at simulated_buy_price
    - Sell at close
    - Profit = close - simulated_buy_price
    """
    buy_signals = df[df['signal'] == 1].copy()
    
    if buy_signals.empty:
        return None
    
    # Average trading value of last 20 sessions: avg(O,H,L,C) × volume
    avg_price = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    trading_value = avg_price * df['volume']
    avg_trading_val_20d = trading_value.tail(20).mean()
    
    # Per-trade P&L
    profits = buy_signals['simulated_profit_pct'].values
    buy_prices = buy_signals['simulated_buy_price'].values
    close_prices = buy_signals['close'].values
    thresholds = buy_signals['dip_threshold'].values
    
    winning = profits[profits > 0]
    losing = profits[profits <= 0]
    
    # Cumulative P&L simulation (compound each trade)
    cumulative_pnl = 0
    for pct in profits:
        trade_pnl = POSITION_SIZE * (pct / 100)
        cumulative_pnl += trade_pnl
    
    return {
        'Symbol': symbol,
        'Avg TradingVal 20D (B)': round(avg_trading_val_20d / 1_000_000_000, 1),
        'Total Signals': len(profits),
        'Win Rate (%)': round(len(winning) / len(profits) * 100, 1) if len(profits) > 0 else 0,
        'Avg Profit (%)': round(np.mean(profits), 2),
        'Median Profit (%)': round(np.median(profits), 2),
        'Best Trade (%)': round(np.max(profits), 2),
        'Worst Trade (%)': round(np.min(profits), 2),
        'Std Dev (%)': round(np.std(profits), 2),
        'Avg Threshold (%)': round(np.mean(thresholds) * 100, 2),
        'Cum P&L (M VND)': round(cumulative_pnl / 1_000_000, 1),
        'Signals/Year': round(len(profits) / (HISTORY_DAYS / 365), 1),
    }


def print_trade_details(df: pd.DataFrame, symbol: str, max_rows: int = 20):
    """Print a detailed view of individual trades and export to CSV."""
    buy_signals = df[df['signal'] == 1].copy()
    
    if buy_signals.empty:
        print(f"  No BUY signals for {symbol}")
        return
    
    detail_cols = ['time', 'prev_close', 'low', 'close', 'dip_threshold', 
                   'simulated_buy_price', 'simulated_profit_pct']
    available_cols = [c for c in detail_cols if c in buy_signals.columns]
    
    detail_df = buy_signals[available_cols].copy()
    
    # Add P&L columns showing how Cum P&L is calculated
    if 'simulated_profit_pct' in detail_df.columns:
        # Per-trade P&L in VND (based on POSITION_SIZE)
        detail_df['trade_pnl_vnd'] = (detail_df['simulated_profit_pct'] / 100 * POSITION_SIZE).astype(int)
        # Running cumulative P&L
        detail_df['cum_pnl_vnd'] = detail_df['trade_pnl_vnd'].cumsum()
    
    # Format for readability
    if 'dip_threshold' in detail_df.columns:
        detail_df['dip_threshold'] = (detail_df['dip_threshold'] * 100).round(2)
        detail_df = detail_df.rename(columns={'dip_threshold': 'threshold_%'})
    if 'simulated_profit_pct' in detail_df.columns:
        detail_df['simulated_profit_pct'] = detail_df['simulated_profit_pct'].round(2)
        detail_df = detail_df.rename(columns={'simulated_profit_pct': 'profit_%'})
    if 'simulated_buy_price' in detail_df.columns:
        detail_df['simulated_buy_price'] = detail_df['simulated_buy_price'].round(0)
        detail_df = detail_df.rename(columns={'simulated_buy_price': 'buy_price'})
    if 'trade_pnl_vnd' in detail_df.columns:
        detail_df = detail_df.rename(columns={'trade_pnl_vnd': 'trade_pnl', 'cum_pnl_vnd': 'cum_pnl'})
    
    # Print to console
    if len(detail_df) > max_rows:
        print(f"\n  --- {symbol}: Last {max_rows} trades (of {len(detail_df)} total) ---")
        print(detail_df.tail(max_rows).to_markdown(index=False))
    else:
        print(f"\n  --- {symbol}: All {len(detail_df)} trades ---")
        print(detail_df.to_markdown(index=False))
    
    # Export to CSV
    import os
    export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "exports")
    os.makedirs(export_dir, exist_ok=True)
    csv_path = os.path.join(export_dir, f"IntradayDip_{symbol}_trades.csv")
    detail_df.to_csv(csv_path, index=False)
    print(f"\n  [Exported] {csv_path}")


def main():
    # Parse symbols
    if len(sys.argv) > 1:
        symbols = sys.argv[1].split(",")
    else:
        symbols = DEFAULT_SYMBOLS

    print(f"{'='*90}")
    print(f"INTRADAY DIP-BUY STRATEGY BACKTEST")
    print(f"{'='*90}")
    print(f"Config: lookback={LOOKBACK_DAYS} days, percentile=P{PERCENTILE:.0f}, "
          f"history={HISTORY_DAYS} days, position={POSITION_SIZE/1e6:.0f}M VND")
    print(f"Stocks: {len(symbols)} symbols\n")

    data_provider = DataProvider(auth=None)
    indicator_engine = IndicatorEngine()
    strategy = IntradayDipStrategy(lookback_days=LOOKBACK_DAYS, percentile=PERCENTILE)

    results = []
    all_dfs = {}  # Store DataFrames for detail view

    for i, symbol in enumerate(symbols):
        print(f"  [{i+1}/{len(symbols)}] Backtesting {symbol}...", end='\r', flush=True)
        try:
            df = data_provider.get_historical_data(symbol, days=HISTORY_DAYS, include_live=False)
            if df.empty:
                continue
            
            # Append standard indicators (strategy doesn't need them, but for consistency)
            df = indicator_engine.append_indicators(df)
            
            # Generate signals
            df = strategy.generate_signals(df)
            
            # Custom P&L calculation
            report = backtest_single_stock(df, symbol)
            if report:
                results.append(report)
                all_dfs[symbol] = df
                
        except Exception as e:
            print(f"  [SKIP] {symbol}: {e}")

    # Print summary table
    print(f"\n\n{'='*90}")
    print(f"BACKTEST RESULTS — IntradayDip(lookback={LOOKBACK_DAYS}, P{PERCENTILE:.0f})")
    print(f"{'='*90}")

    if results:
        df_results = pd.DataFrame(results)
        df_results = df_results.sort_values(by='Win Rate (%)', ascending=False)
        print(df_results.to_markdown(index=False))
        
        # Aggregated summary
        total_signals = df_results['Total Signals'].sum()
        avg_win_rate = df_results['Win Rate (%)'].mean()
        avg_profit = df_results['Avg Profit (%)'].mean()
        total_pnl = df_results['Cum P&L (M VND)'].sum()
        
        print(f"\n{'='*90}")
        print(f"AGGREGATE SUMMARY")
        print(f"{'='*90}")
        print(f"  Total Signals:     {total_signals}")
        print(f"  Avg Win Rate:      {avg_win_rate:.1f}%")
        print(f"  Avg Profit/Trade:  {avg_profit:.2f}%")
        print(f"  Total Cum P&L:     {total_pnl:,.1f}M VND")
        print(f"{'='*90}\n")
        
        # Print detailed trades for single-stock mode
        if len(symbols) <= 3:
            for symbol in symbols:
                if symbol in all_dfs:
                    print_trade_details(all_dfs[symbol], symbol)
        
        return df_results, all_dfs
    else:
        print("[No results — no BUY signals generated]")
        return pd.DataFrame(), {}


if __name__ == "__main__":
    summary, details = main()
