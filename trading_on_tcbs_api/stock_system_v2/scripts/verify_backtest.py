
import os
import sys

# Shim for direct execution
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up 3 levels from scripts/ to repo root
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

from trading_on_tcbs_api.stock_system_v2.core.backtester import Backtester
from trading_on_tcbs_api.stock_system_v2.strategies import (
    SimpleMAStrategy,
    RSIStrategy,
    VolumeBoomStrategy,
    CombinedStrategy,
    DipBuyStrategy
)

def verify():
    print("Initializing Backtester...")
    backtester = Backtester(initial_capital=200_000_000)
    symbol = "HPG"
    days = 730 # Increased to 2 years to ensure MA50 has enough warmup data for early signals
    
    # --- Option 1: Simple MA ---
    # print(f"\n---------- Strategy: MA(20, 50) on {symbol} ----------")
    # strategy = SimpleMAStrategy(short_window=20, long_window=50)
    
    # --- Option 2: RSI (Uncomment to test) ---
    # print(f"\n---------- Strategy: RSI(14) on {symbol} ----------")
    # strategy = RSIStrategy(period=14)

    # --- Option 3: Combined (Uncomment to test) ---
    # --- Option 3: Split Strategy (Buy: MA+Vol, Sell: RSI) ---
    print(f"\n---------- Strategy: Split (Buy=MA+Vol, Sell=RSI) on {symbol} ----------")
    ma = SimpleMAStrategy(short_window=20, long_window=50)
    vol = VolumeBoomStrategy(window=20, threshold_pct=10)
    rsi = RSIStrategy(period=14)
    
    # --- Option 4: Advanced Combined Strategy ---
    # Buy: Price Drops 10% from SMA(20) AND Volume Booms (10% over Vol_SMA)
    # Sell: Price crosses above SMA(20)
    dip_buy = DipBuyStrategy(sma_window=20, drop_pct=2.0)
    vol_boom = VolumeBoomStrategy(window=20, threshold_pct=0.0)
    # Using SimpleMAStrategy inversely as an exit condition 
    # (Sells when short_window (close) crosses ABOVE long_window (SMA20))
    sma_exit = SimpleMAStrategy(short_window=1, long_window=20, invert=True)
    
    strategy = CombinedStrategy(
        strategies=[],
        buy_strategies=[dip_buy, vol_boom], # Require BOTH
        sell_strategies=[sma_exit],         # Only Sell logic
        buy_mode="AND", 
        sell_mode="OR"
    )
    
    
    report = backtester.run(strategy, symbol, days=days)
    
    if not report:
        print("Backtest Failed (No Report returned).")
        return
        
    print("\n[Performance Report]")
    print(f"Symbol: {report['symbol']}")
    print(f"Timeframe:       {report['start_date']} to {report['end_date']} (Last {report['history_days']} days)")
    print(f"Initial Capital: {report['initial_capital']:,.0f} VND")
    print(f"Final Value:     {report['final_value']:,.0f} VND")
    print(f"Total Return:    {report['total_return_pct']:.2f}%")
    print(f"Total Trades:    {report['total_trades']}")
    
    print("\n[Trade Log (Last 20)]")
    for t in report['trades_log'][-20:]:
        print(f"{t['date'].strftime('%Y-%m-%d')} {t['type']} {t['shares']} shares @ {t['price']:,.0f}")

if __name__ == "__main__":
    verify()
