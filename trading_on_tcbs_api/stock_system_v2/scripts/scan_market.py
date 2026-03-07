
import sys
import os

# Shim for direct execution
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)
    __package__ = "stock_system_v2"

from trading_on_tcbs_api.stock_system_v2.core.market_scanner import MarketScanner
from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.strategies.ma_strategy import SimpleMAStrategy
from trading_on_tcbs_api.stock_system_v2.strategies.volume_strategy import VolumeBoomStrategy
from trading_on_tcbs_api.stock_system_v2.strategies.rsi_strategy import RSIStrategy
from trading_on_tcbs_api.stock_system_v2.strategies.combined_strategy import CombinedStrategy

# VN30 List (Approximate)
VN30 = [
    "ACB", "BCM", "BID", "BVH", "CTG", 
    "FPT", "GAS", "GVR", "HDB", "HPG", 
    "MBB", "MSN", "MWG", "PLX", "POW", 
    "SAB", "SHB", "SSB", "SSI", "STB", 
    "TCB", "TPB", "VCB", "VHM", "VIB", 
    "VIC", "VJC", "VNM", "VPB", "VRE"
]

def main():
    print(f"--- DAILY MARKET SCANNER (VN30) ---")
    
    # 0. Initialize Auth (Crucial for Live Data)
    auth = StockAuth()
    if not auth.validate():
        print("[Error] Authentication failed. Exiting.")
        return
    
    # 1. Define Strategy
    ma = SimpleMAStrategy(short_window=20, long_window=50)
    vol = VolumeBoomStrategy(window=20, threshold_pct=10)
    rsi = RSIStrategy(period=14)
    
    # Buy: MA Cross AND Volume Boom
    # Sell: RSI Overbought (Profit Taking)
    strategy = CombinedStrategy(
        strategies=[],
        buy_strategies=[vol],
        sell_strategies=[rsi],
        buy_mode="AND", 
        sell_mode="OR"
    )
    
    # 2. Initialize Scanner with Auth
    scanner = MarketScanner(strategy=strategy, auth=auth)
    
    # 3. Run Scan
    # Use real VN30 list
    symbols = VN30
    
    # Allow overriding symbols via command line args
    if len(sys.argv) > 1:
        symbols = sys.argv[1].split(",")
        
    # results = scanner.scan(symbols)
    # scanner.print_results(results)
    
    # User Request: Produce DataFrame
    df_results = scanner.scan_to_df(symbols)
    
    if not df_results.empty:
        print("\n" + "="*50)
        print("SCAN RESULTS (DataFrame)")
        print("="*50)
        print(df_results.to_markdown(index=False) if hasattr(df_results, 'to_markdown') else df_results)
        print("="*50)
    else:
        print("\n[Scanner] No signals found.")

if __name__ == "__main__":
    main()
