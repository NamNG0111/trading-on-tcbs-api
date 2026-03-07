
import sys
import os


from trading_on_tcbs_api.stock_system_v2.core.market_scanner import MarketScanner
from trading_on_tcbs_api.stock_system_v2.auth.auth import StockAuth
from trading_on_tcbs_api.stock_system_v2.strategies import (
    SimpleMAStrategy,
    VolumeBoomStrategy,
    RSIStrategy,
    CombinedStrategy,
    DipBuyStrategy
)

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
    
    # Buy: Price Drops 10% from SMA(20) AND Volume Booms (10% over Vol_SMA)
    # Sell: Price crosses above SMA(20)
    dip_buy = DipBuyStrategy(sma_window=20, drop_pct=10.0)
    vol_boom = VolumeBoomStrategy(window=20, threshold_pct=10.0)
    sma_exit = SimpleMAStrategy(short_window=1, long_window=20, invert=True)
    
    strategy = CombinedStrategy(
        strategies=[],
        buy_strategies=[dip_buy, vol_boom],
        sell_strategies=[sma_exit],
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
