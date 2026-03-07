
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
from trading_on_tcbs_api.stock_system_v2.strategies.ma_strategy import SimpleMAStrategy
from trading_on_tcbs_api.stock_system_v2.strategies.rsi_strategy import RSIStrategy
from trading_on_tcbs_api.stock_system_v2.strategies.volume_strategy import VolumeBoomStrategy
from trading_on_tcbs_api.stock_system_v2.strategies.combined_strategy import CombinedStrategy
from trading_on_tcbs_api.stock_system_v2.strategies.dip_buy_strategy import DipBuyStrategy

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
    
    # We want:
    # BUY if MA Cross AND Volume Boom
    # SELL if RSI Overbought (ignore MA/Vol for exit)
    # strategy = CombinedStrategy(
    #     strategies=[], # No common strategies
    #     buy_strategies=[ma, vol],
    #     sell_strategies=[rsi],
    #     buy_mode="AND", 
    #     sell_mode="OR"
    # )
    
    # --- Option 4: Dip Buy Strategy (Test New Feature) ---
    print(f"\n---------- Strategy: Dip Buy (SMA 20, Drop 10%) on {symbol} ----------")
    strategy = DipBuyStrategy(sma_window=20, drop_pct=10.0)
    
    
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
