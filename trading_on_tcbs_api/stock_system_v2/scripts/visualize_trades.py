import sys
import pandas as pd
import numpy as np
import mplfinance as mpf
from datetime import datetime

# Import existing backtester and strategies
from trading_on_tcbs_api.stock_system_v2.core.backtester import Backtester
from trading_on_tcbs_api.stock_system_v2.strategies import (
    SimpleMAStrategy,
    VolumeBoomStrategy,
    RSIStrategy,
    CombinedStrategy,
    DipBuyStrategy,
    CumulativeDropStrategy
)

# Reuse the exact strategy definitions from backtest_market
sma_exit_buy_dip = SimpleMAStrategy(short_window=1, long_window=20, invert=True)
sma_exit_basic = SimpleMAStrategy(short_window=1, long_window=20, invert=False)

dip_buy = DipBuyStrategy(sma_window=20, drop_pct=10.0)
strat_dip = CombinedStrategy(
    strategies=[], buy_strategies=[dip_buy], sell_strategies=[sma_exit_buy_dip], buy_mode="AND", sell_mode="OR"
)

vol_buy = VolumeBoomStrategy(window=20, threshold_pct=20.0)
strat_vol = CombinedStrategy(
    strategies=[], buy_strategies=[vol_buy], sell_strategies=[sma_exit_basic], buy_mode="AND", sell_mode="OR"
)

rsi_basic = RSIStrategy(period=14, oversold=30, overbought=70, is_reversal=False)
strat_rsi_basic = CombinedStrategy(
    strategies=[], buy_strategies=[rsi_basic], sell_strategies=[], buy_mode="AND", sell_mode="OR"
)

rsi_reversal = RSIStrategy(period=14, oversold=30, overbought=70, is_reversal=True)
strat_rsi_reversal = CombinedStrategy(
    strategies=[rsi_reversal], buy_strategies=[], sell_strategies=[], buy_mode="AND", sell_mode="OR"
)

roc_buy = CumulativeDropStrategy(days=3, drop_pct=10.0)
strat_roc = CombinedStrategy(
    strategies=[], buy_strategies=[roc_buy], sell_strategies=[], buy_mode="AND", sell_mode="OR"
)

sma_cross = SimpleMAStrategy(short_window=20, long_window=50, invert=False)
strat_sma_cross = CombinedStrategy(
    strategies=[], buy_strategies=[sma_cross, vol_buy], sell_strategies=[sma_cross], buy_mode="AND", sell_mode="OR"
)

my_strategies = {
    f"DipBuy ({dip_buy.drop_pct}%)": strat_dip,
    f"Volume Breakout ({vol_buy.threshold_multiplier * 100 - 100:.0f}%)": strat_vol,
    f"RSI Basic (<{rsi_basic.oversold})": strat_rsi_basic,
    f"RSI Reversal (Entry)": strat_rsi_reversal,
    f"{roc_buy.days}-Day Drop ({roc_buy.drop_pct}%)": strat_roc,
    f"SMA Crossover ({sma_cross.short_window}/{sma_cross.long_window}) + Vol": strat_sma_cross
}

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 -m trading_on_tcbs_api.stock_system_v2.scripts.visualize_trades <SYMBOL> \"<STRATEGY_NAME>\"")
        print("\nAvailable Strategies:")
        for s in my_strategies.keys():
            print(f"  - \"{s}\"")
        return

    symbol = sys.argv[1].upper()
    strat_name = sys.argv[2]

    if strat_name not in my_strategies:
        print(f"Error: Strategy '{strat_name}' not found.")
        return

    print(f"[*] Fetching Data & Backtesting {symbol} using '{strat_name}'...")
    
    # 1. Initialize Backtester
    backtester = Backtester(initial_capital=1_000_000_000)
    strat = my_strategies[strat_name]
    
    # We need the naked dataframe from the Engine to plot over it
    # But backtester.run() abstracts the dataframe away.
    # Let's extract the history again for plotting.
    df = backtester.data_provider.get_historical_data(symbol, days=1825, include_live=False)
    
    if df.empty:
        print("Error: No data found.")
        return

    report = backtester.run(strat, symbol, days=1825, allow_multiple_buys=True)
    
    if not report or 'trades_log' not in report:
        print("No simulation generated.")
        return

    trades = report['trades_log']
    if not trades:
        print(f"[*] No trades executed for {symbol} under this strategy.")
        return

    print(f"[*] Identified {len(trades)} execution signals. Rendering chart...\n")

    # Format DataFrame for mplfinance
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
    
    # To prevent visual clutter spanning 5 years, we can plot the whole thing but let user zoom,
    # or just plot the segment from the first trade to the last trade.
    
    # Create marker arrays 
    # Must be same length as df dataframe, filled with NaN, except for dates with trades
    buy_markers = np.full(len(df), np.nan)
    sell_markers = np.full(len(df), np.nan)

    for trade in trades:
        trade_date = pd.to_datetime(trade['date'])
        # Find the row index for this date
        idx = df.index.get_indexer([trade_date])[0]
        if idx != -1:
            if trade['type'] == 'BUY':
                buy_markers[idx] = df['Low'].iloc[idx] * 0.95 # Place marker slightly below Low
            elif trade['type'] == 'SELL':
                sell_markers[idx] = df['High'].iloc[idx] * 1.05 # Place marker slightly above High

    # Create AddPlots
    ap_buy = mpf.make_addplot(buy_markers, type='scatter', markersize=100, marker='^', color='g', label='BUY')
    ap_sell = mpf.make_addplot(sell_markers, type='scatter', markersize=100, marker='v', color='r', label='SELL')
    
    # Only render if at least one marker
    plots = []
    if not np.isnan(buy_markers).all(): plots.append(ap_buy)
    if not np.isnan(sell_markers).all(): plots.append(ap_sell)

    # Use a handsome visual style with dark background mimicking real trading platform
    style = mpf.make_mpf_style(base_mpf_style='nightclouds', gridstyle=':')
    
    mpf.plot(df, type='candle', style=style,
             title=f"Backtest Executions: {symbol} | Strategy: {strat_name}",
             ylabel='Price (VND)',
             ylabel_lower='Volume',
             volume=True,
             addplot=plots,
             figscale=1.5,
             warn_too_much_data=10000,
             returnfig=False)

if __name__ == "__main__":
    main()
